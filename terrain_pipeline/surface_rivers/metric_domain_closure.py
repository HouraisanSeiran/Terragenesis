"""Window-independent global hydrological closure on the pure physical field.

Why this module exists
---------------------
`hydrology_planning.plan_canonical_support` produces a correct *bounded* product
for one 4L x 4L support, but several of its quantities depend on the window's
bounded extent:

* the ocean is an **in-window** flood seeded from `original < sea_level - MARINE_DEPTH_M`
  (`hydrology_planning.py:174-189`), so a cell connected to the main ocean only
  through a path outside the window is sea in one window and land in another;
* `owner_domain_id` is an `enumerate(sorted(selected_terminals))` index, so the
  same physical domain receives a different integer in every window;
* which cells are accepted at all depends on which terminals the window happens
  to contain.

This module defines the two quantities the window product cannot: a
**window-independent ocean** and a **window-independent outlet identity**, both as
pure functions of `(seed, world coordinate)` on top of the already-pure
`coarse_condition_field`. It deliberately does NOT reuse `plan_macro_cell`: the
in-window logic is exactly what is being replaced.

How window independence is achieved
-----------------------------------
The world is tiled by a fixed lattice of *core tiles* of `core_spans * 4L`. A
query point deterministically selects the tile that contains it (pure function of
the coordinate), and the tile is built with a fixed margin beyond the core. Every
answer for a core cell is therefore identical no matter which query produced it --
there is no caller-supplied window anywhere in this module.

A core cell whose drainage leaves the built (core+margin) extent cannot be
resolved inside the tile and is reported as unresolved (`None`), never guessed.

Drainage model
--------------
Steepest-slope irregular graph on the raw pure field, with `slope > 0` only (same rule as
`hydrology_planning._steepest_receivers`), which makes the receiver graph
strictly downhill and therefore acyclic. The **ocean** is the physical sea:
cells at or below the datum connected to a certified deep-sea core
(`height < sea_level - 100`), i.e. a real connected region -- deliberately NOT
"a cell that drains to the sea", which would label a 2800 m summit as ocean.
Ocean cells are terminals (a river's mouth). A non-ocean local minimum is an
*inland terminal* (a closed basin / lake with no surface outlet) and is a
legitimate finite domain: this module does not fill depressions, unlike the
bounded product which fills and reconnects them. That difference is reported,
not hidden. Candidate-sea cells whose connection to the sea may lie outside the
tile are reported unresolved, never guessed as land.

The raw face is the identity face
---------------------------------
Eligibility, outlet identity and the published surface all live on the **same raw
face** (`self.height` is exactly `coarse_condition_field`, no local correction),
so the two halves of the closure contract cannot contradict each other. This is
the second window-dependence the old planner had, removed by construction rather
than by alignment (see `_build_eligibility` and `tests/test_metric_domain_closure`
`test_published_surface_is_the_pure_base_field`): the planner raised a halo and
reverted it for publication (`hydrology_planning.py:270-290`), which is what made
its published height window-relative (measured max|diff| = 239.51 m between
adjacent windows). Reporting no correction at all is why nothing here can drift
between anchorings. Should a future stage need a real correction, it must itself
be a pure function of `(seed, world coordinate)` and cross-tile bit-identical.
Eligibility (`accepted`, `owner_outlet`) is built on the **same raw face** as
`outlet_at` -- see `ClosureRegion._build_eligibility` for the measurement that
forced it: a *filled* face is window-relative, because both the fill's ocean
seeds and its lake seeds are tile-relative and `_flood` drains toward the tile
border. Building the owner on a filled face while `outlet_at` used the raw face
made the module contradict itself (two anchorings both accepting one cell, with
different owners). The price of the raw face is finer domains than a filled
planner reports; the numbers, and the evidence that the fragmentation is a
property of the base field rather than of the face choice, are recorded in
`_build_eligibility` -- reported, not hidden.
"""
from __future__ import annotations

import numpy as np

from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.drainage import strict_receivers as strict_receivers

from terrain_pipeline.hydrology_planning import (
    MARINE_DEPTH_M,
    PlanningConfig,
    coarse_condition_field,
)

__all__ = [
    "MARINE_DEPTH_M",
    "ClosureRegion",
    "outlet_at",
    "global_ocean_mask",
    "territory_of",
    "territory_id_at",
    "resolve_points",
    "eligible_owner_at",
    "owner_grid",
    "domain_topology",
    "clear_cache",
]


# `MARINE_DEPTH_M` is re-exported from `hydrology_planning`, the single
# authority (it used to be a second copy right here). Every calculation below
# reads `config.marine_depth_m`, whose default is that constant, so changing the
# parameter moves the answer and the identity together.

# Default tile geometry. core_spans * macro_span_m = 4L = 1280 km core; the
# margin is 48 nodes = 480 km of drainage headroom beyond the core.
DEFAULT_CORE_SPANS = 4
DEFAULT_MARGIN_NODES = 48

_CACHE: dict = {}


def _steepest_graph(height, *, mesh=None, x0_m=0., z0_m=0., spacing_m=30., world_seed=20261020):
    """Strict positive metric slopes on the shared irregular cell graph."""
    mesh = grid_mesh(height.shape, x0_m=x0_m, z0_m=z0_m, dx_m=spacing_m,
                     world_seed=world_seed) if mesh is None else mesh
    receiver, _, _ = strict_receivers(height, mesh)
    return receiver.reshape(height.shape)

def _terminal_of(receiver, height):
    """Terminal index per cell: follow the strictly-downhill receiver chain.

    Ascending-height order guarantees `terminal[receiver[i]]` is already known
    when `i` is processed, because the receiver is strictly lower.
    """
    flat_receiver = receiver.reshape(-1)
    flat_height = height.reshape(-1)
    terminal = np.full(flat_height.size, -1, np.int64)
    for position in np.argsort(flat_height, kind="stable"):
        downstream = flat_receiver[position]
        terminal[position] = position if downstream < 0 else terminal[downstream]
    return terminal.reshape(height.shape)


def _reaches_border(receiver, height, border):
    """Cells whose strictly-downhill chain (itself included) hits a border node.

    A border node has fewer than complete supported graph neighbourhood, so its steepest-slope
    receiver is not the physical one: the chain may be heading for a different
    terminal than the one visible inside the tile. A chain routed through such a
    node is therefore untrustworthy and refused -- at *every* anchoring, so the
    refusal set is itself a pure function of `(seed, world coordinate)`.

    Ascending-height order guarantees `reaches[receiver[i]]` is already final
    when `i` is processed (the receiver is strictly lower, see `_steepest_graph`).
    """
    flat_receiver = receiver.reshape(-1)
    flat_height = height.reshape(-1)
    reaches = border.reshape(-1).copy()
    for position in np.argsort(flat_height, kind="stable"):
        downstream = flat_receiver[position]
        if downstream >= 0:
            reaches[position] |= reaches[downstream]
    return reaches.reshape(border.shape)


def _reverse_flood(receiver, terminal, target_terminal):
    """Cells whose terminal is `target_terminal`, by one pass over all cells."""
    return terminal == target_terminal


def _territory_mask(ocean, terminal, target_terminal):
    """Land cells whose drainage terminates at `target_terminal`.

    Ocean cells are excluded, including the marine mouth itself: a sea cell has no
    upstream outlet of its own (`outlet_at` refuses it), so including it would make
    a marine territory contain a cell that does not drain back to the outlet.
    """
    return (~ocean) & _reverse_flood(None, terminal, target_terminal)


class ClosureRegion:
    """One world-anchored tile: pure field -> ocean / outlet / territory.

    All world coordinates are metre coordinates on the same axes as
    `coarse_condition_field`. Node `(row, col)` sits at
    `(origin_x_m + col * spacing_m, origin_z_m + row * spacing_m)`.
    """

    def __init__(self, seed, config, region_row, region_col):
        self.seed = int(seed)
        self.config = config
        self.spacing_m = float(config.macro_span_m / config.samples_per_span)
        self.sea_level_m = float(config.sea_level_m)
        core_cells = int(DEFAULT_CORE_SPANS * config.samples_per_span)
        margin = int(DEFAULT_MARGIN_NODES)
        self.core_cells = core_cells
        self.margin = margin
        self.region_row = int(region_row)
        self.region_col = int(region_col)

        core_span_m = core_cells * self.spacing_m
        self.core_origin_x_m = self.region_col * core_span_m
        self.core_origin_z_m = self.region_row * core_span_m
        self.origin_x_m = self.core_origin_x_m - margin * self.spacing_m
        self.origin_z_m = self.core_origin_z_m - margin * self.spacing_m
        self.shape = (core_cells + 1 + 2 * margin, core_cells + 1 + 2 * margin)

        rows, columns = self.shape
        axis_x = self.origin_x_m + np.arange(columns) * self.spacing_m
        axis_z = self.origin_z_m + np.arange(rows) * self.spacing_m
        grid_x, grid_z = np.meshgrid(axis_x, axis_z)
        height, _, _ = coarse_condition_field(self.seed, grid_x, grid_z, config)
        self.height = np.asarray(height, np.float64)

        # The ocean is the PHYSICAL sea: cells at or below the datum that are
        # connected over the irregular graph to a certified deep-sea core. It is NOT
        # "drains to a marine terminal" -- that would label a 2800 m summit that
        # drains to the coast as ocean (measured: 17586 of 35688 such cells are
        # land, heights up to 2804 m). Connectivity is what the contract asks for
        # and it is the only definition comparable with the bounded planner's
        # in-window flood.
        self.marine = self.height < (self.sea_level_m - config.marine_depth_m)
        self.negative = self.height <= self.sea_level_m
        # The four-cell band lacks complete bounded-radius triangulation support,
        # so neither its steepest-slope receiver nor a sea
        # connection routed through it is the physical one.
        self.border = np.zeros(self.shape, bool)
        self.border[:4, :] = True
        self.border[-4:, :] = True
        self.border[:, :4] = True
        self.border[:, -4:] = True
        self.mesh = grid_mesh(self.shape, x0_m=self.origin_x_m, z0_m=self.origin_z_m,
                              dx_m=self.spacing_m, world_seed=self.seed)
        self.ocean, self.ocean_uncertain = self._flood_ocean()

        # Land drainage: strictly-downhill irregular graph on the raw field; sea cells are
        # terminals (a river's mouth), inland local minima are closed basins.
        self.receiver = _steepest_graph(self.height, mesh=self.mesh)
        self.receiver[self.ocean] = -1
        self.terminal = _terminal_of(self.receiver, self.height)
        self.terminal_ocean = self.ocean.reshape(-1)[self.terminal.reshape(-1)].reshape(self.shape)
        # Any chain routed through the truncated ring is refused (see
        # `_compute_unresolved`); the stored mask keeps that refusal a pure
        # function of the world coordinate.
        self.chain_reaches_border = _reaches_border(self.receiver, self.height, self.border)

        in_core = np.zeros(self.shape, bool)
        in_core[margin:margin + core_cells + 1, margin:margin + core_cells + 1] = True
        self.in_core = in_core
        self.unresolved = self._compute_unresolved()

        # World-anchored eligibility: which cells belong to a CLOSED domain, and
        # which domain (identified by its outlet world coordinate). Built on the
        # filled face with the bounded planner's discipline -- see
        # `_build_eligibility`.
        self.accepted, self.owner_outlet, self.owner_index = self._build_eligibility()

    def _flood_ocean(self):
        """Connected below-datum region containing certified deep sea.

        Returns ``(ocean, uncertain)``.

        ``uncertain`` marks every candidate-sea cell (at or below the datum) whose
        connection to the world sea is not decided inside the tile: the flood could
        not reach it, but it is connected, through other candidate-sea cells, to a
        candidate-sea node on the built border, where the true connection may
        continue outside. Those cells must be reported as unknown, never as land.

        Such components are *swallowed* here -- marked non-ocean, i.e. land -- before
        the uncertain mask is built, because the connectivity that would feed a
        neighbouring tile's flood has to be visible: a tile whose certified deep sea
        lies beyond a wide strait would otherwise call every cell of that strait
        unknown, while still flooding its own ocean through it. Swallowing and the
        precise uncertain mask make `(ocean, uncertain)` a function of the world
        coordinate, so two anchorings cannot disagree about a shared candidate-sea
        cell.
        """
        shape = self.shape
        ocean = np.zeros(self.height.size, bool)
        negative = self.negative.ravel()
        pending = list(np.flatnonzero(self.marine))
        while pending:
            cell = pending.pop()
            if ocean[cell]:
                continue
            ocean[cell] = True
            for edge in range(self.mesh.indptr[cell], self.mesh.indptr[cell + 1]):
                target = int(self.mesh.indices[edge])
                if negative[target] and not ocean[target]:
                    pending.append(target)
        uncertain = np.zeros(ocean.size, bool)
        remaining = negative & ~ocean
        for start in np.flatnonzero(remaining):
            if not remaining[start]:
                continue
            component = []
            touches_border = False
            pending = [int(start)]
            remaining[start] = False
            while pending:
                cell = pending.pop()
                component.append(cell)
                touches_border |= bool(self.border.ravel()[cell])
                for edge in range(self.mesh.indptr[cell], self.mesh.indptr[cell + 1]):
                    target = int(self.mesh.indices[edge])
                    if remaining[target]:
                        remaining[target] = False
                        pending.append(target)
            if touches_border:
                uncertain[component] = True
        return ocean.reshape(shape), uncertain.reshape(shape)

    def _compute_unresolved(self):
        """Cells whose answer cannot be trusted, in the contract's vocabulary.

        A cell is refused when its strictly-downhill chain is not fully determined
        by the built tile:

        * the chain reaches a **border** node, whose steepest-slope receiver was
          computed with fewer than complete supported graph neighbourhood. The chain may in truth
          leave the tile there and end at a different terminal, so no answer is
          given -- this covers both a chain merely *routing through* the truncated
          ring and one ending at a border terminal, marine or inland;
        * a candidate-sea cell whose connection to the world sea is not decided
          inside the tile (see `_flood_ocean`): it is unknown, never land.

        A chain that stays strictly inside the built tile is trustworthy: every node
        it visits has its complete graph neighbourhood in-tile, so "no strictly-lower
        neighbour" really is a physical local minimum (a closed basin) and a marine
        terminal really is the mouth. The refusal set is a pure function of
        `(seed, world coordinate)`, so the same physical cell is refused at every
        anchoring that can see it: no caller ever sees a guessed outlet, and two
        anchorings can never disagree.
        """
        refused = (self.chain_reaches_border & ~self.ocean) | self.ocean_uncertain
        return refused

    def _build_eligibility(self):
        """World-anchored eligibility on the **same raw face** as `outlet_at`.

        Returns ``(accepted, owner_outlet, owner_index)``.

        Identity is the raw-field terminal's world coordinate (`world_of_terminal`
        of `self.terminal`) -- exactly what `outlet_at` returns, so the two halves
        of the contract cannot contradict each other::

            accepted  <=>  owner_at(point) is not None
                      and owner_at(point) == outlet_at(point)

        The RAW face versus the filled face -- both directions, measured
        ---------------------------------------------------------------
        The bounded planner builds its owner on a **filled** face
        (`hydrology_planning.py:199-231`). Copying that here was tried and is
        wrong, measured -- the fill itself is window-relative, because both of its
        seeds are tile-relative:

        * the fill is seeded from the tile's own certified sea, and `_flood`
          grows the filled surface by draining *toward the tile border* (the
          border acts as the outlet), so two tiles raise overlapping cells to
          different levels;
        * the lake seeds are the tile's own complete interior depressions.

        Measured consequence: a cell at world (440000, 200000) has identical raw
        elevation 530.282 m in both tiles, yet the two filled faces terminate it
        at different outlets -- `owner_outlet` = (460000, 160000) from one
        anchoring and (460000, 270000) from the other, while `outlet_at` agreed on
        (460000, 250000). Two anchorings both *accepting* the cell with different
        owners is a self-contradiction, and it is exactly what an audit found.
        The raw field is a pure function of `(seed, world coordinate)`, so a raw
        terminal is the same physical point from every anchoring that can see the
        chain, and the contradiction cannot arise.

        The cost of the raw face -- reported, not hidden
        ------------------------------------------------
        Not filling makes domains finer than a filled planner's: a local pit is a
        legitimate finite `closed_basin` instead of being drained into its
        neighbour. Measured over four tiles (seed 20261020): domain size median
        **3 cells (30 km)**, mean 9.1-9.4, 24-26 % of domains a single cell, and
        47-50 % of accepted cells terminate at an inland (non-marine) minimum.
        A planner-style fill does *not* repair this: it leaves the median at 3 and
        *raises* the single-cell share to 28-31 %, because a filled pit becomes a
        near-flat platform on which steepest-slope irregular graph still cannot order cells.
        The fragmentation is a property of the base field (`coarse_condition_field`
        carries many 10-30 km local structures), not of the face choice; natural
        domain coarsening is a separate line and is not solved here. What this
        module promises is narrower: whichever domains it reports are
        window-independent.

        A cell is accepted exactly when its chain was decided inside the tile and
        the cell is land (`~unresolved & ~ocean`) -- the module's `coastal` /
        `closed_basin` vocabulary. A closed basin is a legitimate finite domain: a
        pit strictly inside the tile has all its neighbours in-tile, so "no
        strictly-lower neighbour" is a physical fact, not a truncation artefact.
        """
        shape = self.shape
        flat_ocean = self.ocean.reshape(-1)
        flat_unresolved = self.unresolved.reshape(-1)
        terminal_flat = self.terminal.reshape(-1)
        accepted_flat = (~flat_ocean) & (~flat_unresolved)

        owner_outlet = np.full(shape + (2,), np.nan)
        owner_index = np.full(shape, -1, np.int64)
        if accepted_flat.any():
            accepted_terminals = np.unique(terminal_flat[accepted_flat])
            coordinates = np.array([self.world_of_terminal(int(t))
                                    for t in accepted_terminals], np.float64)
            rank = {int(t): position for position, t in enumerate(accepted_terminals)}
            owner_index_flat = np.full(terminal_flat.size, -1, np.int64)
            for position in np.flatnonzero(accepted_flat):
                owner_index_flat[position] = rank[int(terminal_flat[position])]
            owner_index = owner_index_flat.reshape(shape)
            rows, columns = np.nonzero(accepted_flat.reshape(shape))
            owner_outlet[rows, columns] = coordinates[owner_index[rows, columns]]
        return accepted_flat.reshape(shape), owner_outlet, owner_index

    def eligible_at(self, x_m, z_m):
        """True when the point belongs to a closed domain decided inside the tile."""
        row, column = self._node(x_m, z_m)
        row, column = int(row), int(column)
        if not (0 <= row < self.shape[0] and 0 <= column < self.shape[1]):
            return False
        return bool(self.accepted[row, column])

    def owner_at(self, x_m, z_m):
        """Outlet world coordinate of the domain owning a point, or None.

        `None` covers the sea (no upstream outlet) and every cell that is not
        part of a domain closed inside this tile -- it is never a guess.
        """
        row, column = self._node(x_m, z_m)
        row, column = int(row), int(column)
        if not (0 <= row < self.shape[0] and 0 <= column < self.shape[1]):
            return None
        if not bool(self.accepted[row, column]):
            return None
        return (float(self.owner_outlet[row, column, 0]),
                float(self.owner_outlet[row, column, 1]))

    def _node(self, x_m, z_m):
        column = np.round((np.asarray(x_m, np.float64) - self.origin_x_m) / self.spacing_m).astype(np.int64)
        row = np.round((np.asarray(z_m, np.float64) - self.origin_z_m) / self.spacing_m).astype(np.int64)
        return row, column

    def world_of_terminal(self, terminal_flat_index):
        rows, columns = self.shape
        row, column = np.divmod(int(terminal_flat_index), columns)
        return (self.origin_x_m + column * self.spacing_m,
                self.origin_z_m + row * self.spacing_m)

    def outlet_at(self, x_m, z_m):
        """Outlet world coordinates for a world point, or None when unresolved.

        `None` covers three cases the contract keeps distinct: the point is outside
        the built tile, the point is **sea** (it has no upstream outlet of its own --
        the mouth is where the land ends, not the sea), and the point's chain cannot
        be closed inside the tile (never guessed). Use `classify` for the reason.
        """
        row, column = self._node(x_m, z_m)
        row = int(row)
        column = int(column)
        if not (0 <= row < self.shape[0] and 0 <= column < self.shape[1]):
            return None
        if self.unresolved[row, column] or self.ocean[row, column]:
            return None
        return self.world_of_terminal(self.terminal[row, column])

    def ocean_at(self, x_m, z_m):
        row, column = self._node(x_m, z_m)
        row, column = int(row), int(column)
        if not (0 <= row < self.shape[0] and 0 <= column < self.shape[1]):
            return None
        return bool(self.ocean[row, column])

    def classify(self, x_m, z_m):
        """Reason code for a world point (unambiguous vocabulary).

        * ``ocean``            - the cell itself is sea (connected below datum).
        * ``coastal``          - land whose chain reaches the sea: a normal,
          resolved domain whose outlet is the river mouth.
        * ``closed_basin``     - land whose chain ends at an inland minimum strictly
          inside the tile: a legitimate finite domain with no surface outlet.
        * ``unresolved_border`` - the chain (or the sea connection) may leave the
          tile, so no answer is given. This is the refusal case; the module never
          guesses an outlet or calls such a cell land.
        * ``out_of_tile``      - outside this built extent.
        """
        row, column = self._node(x_m, z_m)
        row, column = int(row), int(column)
        if not (0 <= row < self.shape[0] and 0 <= column < self.shape[1]):
            return "out_of_tile"
        if self.unresolved[row, column]:
            return "unresolved_border"
        if bool(self.ocean[row, column]):
            return "ocean"
        if bool(self.terminal_ocean[row, column]):
            return "coastal"
        return "closed_basin"

    def territory_of_outlet(self, outlet_x_m, outlet_z_m):
        """LAND cells (world coordinates) whose drainage terminates at the outlet.

        The outlet coordinate is matched to the nearest terminal node, so callers
        can pass a coordinate returned by `outlet_at` verbatim. The outlet cell
        itself is part of the territory when it is land (a lake spill terminal); a
        marine mouth is sea, so it is not a territory cell -- every returned cell
        is land whose own `outlet_at` is this outlet.
        """
        row, column = self._node(outlet_x_m, outlet_z_m)
        row, column = int(row), int(column)
        if not (0 <= row < self.shape[0] and 0 <= column < self.shape[1]):
            return None
        target = int(self.terminal[row, column])
        if bool(self.terminal_ocean.reshape(-1)[target]):
            kind = "marine"
        else:
            kind = "inland"
        mask = _territory_mask(self.ocean, self.terminal, target)
        rows, columns = np.nonzero(mask & self.in_core)
        x = self.core_origin_x_m + (columns - self.margin) * self.spacing_m
        z = self.core_origin_z_m + (rows - self.margin) * self.spacing_m
        return {
            "outlet_xz_m": self.world_of_terminal(target),
            "kind": kind,
            "cell_count": int(rows.size),
            "cells_x_m": x,
            "cells_z_m": z,
            "area_m2": float(rows.size * self.spacing_m ** 2),
        }


def _region_key(seed, config):
    return (int(seed), float(config.macro_span_m), int(config.samples_per_span),
            float(config.sea_level_m), float(config.marine_depth_m),
            int(DEFAULT_CORE_SPANS), int(DEFAULT_MARGIN_NODES))


def _region_for_point(seed, x_m, z_m, config):
    """Deterministically pick (and cache) the world-anchored tile containing a point."""
    spacing = config.macro_span_m / config.samples_per_span
    core_span_m = DEFAULT_CORE_SPANS * config.samples_per_span * spacing
    column = int(np.floor(x_m / core_span_m))
    row = int(np.floor(z_m / core_span_m))
    key = _region_key(seed, config) + (row, column)
    region = _CACHE.get(key)
    if region is None:
        region = ClosureRegion(seed, config, row, column)
        _CACHE[key] = region
    return region


def outlet_at(seed, x_m, z_m, config=None):
    """Window-independent outlet: pure function of `(seed, world coordinate)`.

    Returns `(outlet_x_m, outlet_z_m)` -- the world coordinate of the terminal the
    point drains to -- or `None` when the point is ocean, or its drainage cannot
    be resolved inside its world-anchored tile (never guessed).
    """
    config = config or PlanningConfig()
    config.validate()
    scalar = np.ndim(x_m) == 0 and np.ndim(z_m) == 0
    xs = np.atleast_1d(np.asarray(x_m, np.float64))
    zs = np.atleast_1d(np.asarray(z_m, np.float64))
    if xs.shape != zs.shape:
        xs, zs = np.broadcast_arrays(xs, zs)
    out_x = np.full(xs.shape, np.nan)
    out_z = np.full(xs.shape, np.nan)
    for position in range(xs.size):
        region = _region_for_point(seed, float(xs.reshape(-1)[position]),
                                   float(zs.reshape(-1)[position]), config)
        answer = region.outlet_at(float(xs.reshape(-1)[position]), float(zs.reshape(-1)[position]))
        if answer is not None:
            out_x.reshape(-1)[position] = answer[0]
            out_z.reshape(-1)[position] = answer[1]
    if scalar:
        if np.isnan(out_x.reshape(-1)[0]):
            return None
        return (float(out_x.reshape(-1)[0]), float(out_z.reshape(-1)[0]))
    return (out_x, out_z)


def global_ocean_mask(seed, x_grid, z_grid, config=None):
    """Window-independent ocean mask: is the point itself the physical sea?

    Returns a boolean array shaped like the broadcast grids; `False` where the
    point's classification is unresolved (callers should treat that as unknown,
    not as land). This is the *connected* sea (`ClosureRegion.ocean`), not
    "drains to a marine terminal": a summit that drains to the coast is land.
    """
    config = config or PlanningConfig()
    config.validate()
    xs = np.atleast_1d(np.asarray(x_grid, np.float64))
    zs = np.atleast_1d(np.asarray(z_grid, np.float64))
    xs, zs = np.broadcast_arrays(xs, zs)
    ocean = np.zeros(xs.shape, bool)
    for position in range(xs.size):
        region = _region_for_point(seed, float(xs.reshape(-1)[position]),
                                   float(zs.reshape(-1)[position]), config)
        answer = region.ocean_at(float(xs.reshape(-1)[position]), float(zs.reshape(-1)[position]))
        ocean.reshape(-1)[position] = bool(answer)
    return ocean


def territory_of(seed, outlet_x_m, outlet_z_m, config=None):
    """Territory of the outlet nearest a world coordinate (see ClosureRegion)."""
    config = config or PlanningConfig()
    config.validate()
    region = _region_for_point(seed, float(outlet_x_m), float(outlet_z_m), config)
    return region.territory_of_outlet(float(outlet_x_m), float(outlet_z_m))


def territory_id_at(seed, x_m, z_m, config=None):
    """Stable territory identity at a point: its outlet world coordinate, or None."""
    return outlet_at(seed, x_m, z_m, config)


def resolve_points(seed, x_m, z_m, config=None):
    """Batch helper: outlet, ocean, resolved flag and a per-point reason code.

    The `reason` array makes every refusal auditable in a fixed vocabulary (see
    `ClosureRegion.classify`: `ocean` / `coastal` / `closed_basin` /
    `unresolved_border` / `out_of_tile`), so callers never have to infer *why* a
    point had no outlet: `resolved` is False exactly where `reason` is
    `unresolved_border` or `out_of_tile`. A point in the sea is *resolved* (the
    world is known there) yet carries no outlet, so `resolved` is not the same as
    "has an outlet".
    """
    config = config or PlanningConfig()
    config.validate()
    xs = np.atleast_1d(np.asarray(x_m, np.float64))
    zs = np.atleast_1d(np.asarray(z_m, np.float64))
    xs, zs = np.broadcast_arrays(xs, zs)
    flat_x, flat_z = xs.reshape(-1), zs.reshape(-1)
    outlet_x = np.full(xs.shape, np.nan)
    outlet_z = np.full(xs.shape, np.nan)
    ocean = np.zeros(xs.shape, bool)
    reasons = np.empty(xs.shape, dtype=object)
    for position in range(flat_x.size):
        xp, zp = float(flat_x[position]), float(flat_z[position])
        region = _region_for_point(seed, xp, zp, config)
        reasons.reshape(-1)[position] = region.classify(xp, zp)
        ocean.reshape(-1)[position] = bool(region.ocean_at(xp, zp))
        answer = region.outlet_at(xp, zp)
        if answer is not None:
            outlet_x.reshape(-1)[position] = answer[0]
            outlet_z.reshape(-1)[position] = answer[1]
    resolved = np.isfinite(outlet_x) | ocean
    return {"outlet_x_m": outlet_x, "outlet_z_m": outlet_z,
            "ocean": ocean, "resolved": resolved, "reason": reasons}


def eligible_owner_at(seed, x_m, z_m, config=None):
    """World-anchored eligibility and outlet identity for a world point.

    Returns ``(accepted, outlet_xz)``: whether the point belongs to a domain closed
    inside its world-anchored tile, and that domain's outlet world coordinate (the
    identity of the domain) or `None` when the point is not accepted. Both are pure
    functions of `(seed, world coordinate)` -- the caller supplies no window.
    """
    config = config or PlanningConfig()
    config.validate()
    scalar = np.ndim(x_m) == 0 and np.ndim(z_m) == 0
    xs = np.atleast_1d(np.asarray(x_m, np.float64))
    zs = np.atleast_1d(np.asarray(z_m, np.float64))
    if xs.shape != zs.shape:
        xs, zs = np.broadcast_arrays(xs, zs)
    accepted = np.zeros(xs.shape, bool)
    out_x = np.full(xs.shape, np.nan)
    out_z = np.full(xs.shape, np.nan)
    flat_x, flat_z = xs.reshape(-1), zs.reshape(-1)
    for position in range(flat_x.size):
        xp, zp = float(flat_x[position]), float(flat_z[position])
        region = _region_for_point(seed, xp, zp, config)
        if not region.eligible_at(xp, zp):
            continue
        answer = region.owner_at(xp, zp)
        accepted.reshape(-1)[position] = True
        out_x.reshape(-1)[position] = answer[0]
        out_z.reshape(-1)[position] = answer[1]
    if scalar:
        if not bool(accepted.reshape(-1)[0]):
            return False, None
        return True, (float(out_x.reshape(-1)[0]), float(out_z.reshape(-1)[0]))
    return accepted, (out_x, out_z)


def owner_grid(seed, x_grid, z_grid, config=None):
    """Vectorised `eligible_owner_at`: acceptance mask plus outlet identity grid.

    Returns ``{"accepted": bool array, "outlet_x_m": array, "outlet_z_m": array}``
    shaped like the broadcast grids; the outlet arrays are NaN and `accepted` is
    False wherever the point is not part of a closed domain.
    """
    config = config or PlanningConfig()
    config.validate()
    xs = np.atleast_1d(np.asarray(x_grid, np.float64))
    zs = np.atleast_1d(np.asarray(z_grid, np.float64))
    xs, zs = np.broadcast_arrays(xs, zs)
    accepted, (out_x, out_z) = eligible_owner_at(seed, xs, zs, config)
    accepted = np.asarray(accepted, bool).reshape(xs.shape)
    return {"accepted": accepted,
            "outlet_x_m": np.asarray(out_x, np.float64).reshape(xs.shape),
            "outlet_z_m": np.asarray(out_z, np.float64).reshape(xs.shape)}


def domain_topology(seed, x_m, z_m, config=None):
    """Read-only raw-face routing of the world-anchored tile holding a point.

    This is a **pure addition**: it exposes arrays the closure module already
    computes and owns, so a consumer (the domain-flow ledger, an auditor) never
    has to author a second flood or a second steepest irregular-graph pass -- a second
    implementation would be a second truth that can drift from the one the
    auditor certifies. No existing function's signature or behaviour changes.

    Every returned array is a **copy**: mutating one cannot corrupt `_CACHE` or
    change any later answer. Coordinates are metres on the same axes as the
    public queries. Account centers use the declared origin and spacing;
    `node_x_m` and `node_z_m` expose their continuous graph representatives.
    Flat indices are `row * shape[1] + column`.

    Keys:

    * `receiver` - flat index of the strictly-downhill steepest neighbour, `-1`
      at a terminal (ocean cell or inland local minimum);
    * `height_m` - the RAW pure base face (`coarse_condition_field`) this tile's
      routing was built on, with no local correction (the same face the products
      publish as `base_height_m`);
    * `terminal` - flat index of the terminal each cell drains to
      (`terminal == own index` for a terminal cell);
    * `ocean` - the connected physical sea (below datum, connected to certified
      deep sea), the same mask `global_ocean_mask` answers pointwise;
    * `ocean_terminal` - `True` where the terminal of a cell is ocean, i.e. the
      domain is a coastal one whose outlet is a river mouth;
    * `unresolved` - the refusal set (`unresolved_border`): the chain, or the
      sea connection, may leave the built tile. Never guessed as land or sea;
    * `accepted` - `~ocean & ~unresolved`: the land cells whose answer was
      decided inside the tile (the `coastal` / `closed_basin` vocabulary);
    * `owner_outlet_x_m` / `owner_outlet_z_m` - the accepting domain's outlet
      world coordinate, `NaN` where the cell is not accepted;
    * `in_core` - the tile's core (the published territory is clipped to it);
    * geometry: `origin_x_m`, `origin_z_m`, `spacing_m`, `shape`,
      `core_origin_x_m`, `core_origin_z_m`, `core_cells`, `margin`, `seed`.
    """
    config = config or PlanningConfig()
    config.validate()
    region = _region_for_point(seed, float(x_m), float(z_m), config)
    owner = region.owner_outlet
    return {
        "seed": int(region.seed),
        "spacing_m": float(region.spacing_m),
        "shape": tuple(int(size) for size in region.shape),
        "origin_x_m": float(region.origin_x_m),
        "origin_z_m": float(region.origin_z_m),
        "core_origin_x_m": float(region.core_origin_x_m),
        "core_origin_z_m": float(region.core_origin_z_m),
        "core_cells": int(region.core_cells),
        "margin": int(region.margin),
        "receiver": region.receiver.astype(np.int64, copy=True),
        "node_x_m": region.mesh.node_x_m.reshape(region.shape).copy(),
        "node_z_m": region.mesh.node_z_m.reshape(region.shape).copy(),
        "height_m": np.array(region.height, np.float64, copy=True),
        "terminal": region.terminal.astype(np.int64, copy=True),
        "ocean": region.ocean.copy(),
        "ocean_terminal": region.terminal_ocean.copy(),
        "unresolved": region.unresolved.copy(),
        "accepted": region.accepted.copy(),
        "owner_outlet_x_m": np.array(owner[:, :, 0], np.float64, copy=True),
        "owner_outlet_z_m": np.array(owner[:, :, 1], np.float64, copy=True),
        "in_core": region.in_core.copy(),
    }


def clear_cache():
    _CACHE.clear()
